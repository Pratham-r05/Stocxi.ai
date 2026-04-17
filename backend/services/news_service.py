"""
news_service.py — Recent news headlines for a stock symbol.

AI_CONTEXT.md spec: "News | yfinance .news property | Good enough for phase 1"

Reality: yfinance .news also hits crumb-gated endpoints and 429s with our IP.

Fix: Primary source = ScanX stock-news pages
    URL: https://scanx.trade/stock-news/{company-slug}
    - Parse Angular SSR ng-state JSON for company-specific latest stories
    - Build stable article links: /stock-market-news/{category}/{slug}/{id}
    - Keep only last 7 days for genuinely recent headlines

Fallback 1: Google News RSS
  URL: https://news.google.com/rss/search?q={symbol}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en
  - Completely free, no auth, no API key, no rate limits
  - Returns real financial news in English, India-focused
  - Parse with stdlib xml.etree (no extra deps)

Fallback 2: yfinance .news (works when Yahoo isn't throttling)
Fallback 3: Empty list (never crash)

Cache TTL: 7200s (2 hrs) — set in redis_client.py TTL_NEWS
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape
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
_NEWS_MAX_AGE_DAYS = 30  # only show news from last 30 days
_SCANX_MAX_AGE_DAYS = 7  # ScanX feed targets latest 1 week
_SCANX_TARGET_MIN_NEWS = 7  # user-facing floor when enough ScanX history exists
_SCANX_BASE_URL = "https://scanx.trade"


def _parse_published_datetime(published: str | None) -> datetime | None:
    """Parse published timestamp into UTC datetime, supporting common formats."""
    if not published:
        return None

    raw = str(published).strip()
    if not raw:
        return None

    # Epoch seconds support (e.g. "1713163200" or "1713163200.0").
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except Exception:
            return None

    # ISO-8601 support, including trailing Z.
    try:
        iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # RFC-style news dates.
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue

    return None


def _sort_news_articles(articles: list[dict]) -> list[dict]:
    """Sort articles by published datetime (newest first, unknown dates last)."""
    return sorted(
        list(articles),
        key=lambda item: _parse_published_datetime(item.get("published"))
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def _is_recent_news(published_iso: str, max_age_days: int = _NEWS_MAX_AGE_DAYS) -> bool:
    """Return True if article was published within the provided age window."""
    if not published_iso:
        return True  # keep if date unknown
    try:
        dt_str = str(published_iso).strip()
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        return dt >= cutoff
    except Exception:
        return True  # keep on parse failure


def _is_relevant_news_title(title: str, symbol: str, company_name: str | None = None) -> bool:
    """Keep only headlines clearly tied to the requested stock/company."""
    text = str(title or "").strip()
    if not text:
        return False

    low = text.lower()
    broad_noise = [
        "stocks to watch",
        "top brokerage ratings",
        "market wrap",
        "sensex",
        "nifty today",
        "share market live",
        "pre-open",
    ]

    symbol_l = symbol.lower().strip()
    has_symbol = bool(symbol_l and re.search(rf"\b{re.escape(symbol_l)}\b", low))

    company_l = str(company_name or "").lower().strip()
    company_tokens = [
        tok for tok in re.split(r"[^a-z0-9]+", company_l)
        if tok and len(tok) >= 4 and tok not in {"limited", "india", "group", "ltd", "plc"}
    ]
    token_hits = sum(1 for tok in company_tokens if re.search(rf"\b{re.escape(tok)}\b", low))
    has_company = token_hits >= 1 or (company_l and company_l in low)

    # Many Indian headlines use short company aliases (e.g., HUL, RIL, TCS).
    # Build acronym candidates from company name so these titles are retained.
    acronym_candidates: set[str] = set()
    company_words = [tok for tok in re.split(r"[^a-z0-9]+", company_l) if tok]
    if len(company_words) >= 2:
        acronym_full = "".join(tok[0] for tok in company_words if tok)
        if len(acronym_full) >= 3:
            acronym_candidates.add(acronym_full)

        core_words = [
            tok for tok in company_words
            if tok not in {"limited", "ltd", "plc", "inc", "corp", "corporation", "co", "company", "india"}
        ]
        if len(core_words) >= 2:
            acronym_core = "".join(tok[0] for tok in core_words if tok)
            if len(acronym_core) >= 3:
                acronym_candidates.add(acronym_core)

    has_company_alias = any(
        re.search(rf"\b{re.escape(alias)}\b", low)
        for alias in acronym_candidates
    )

    if not (has_symbol or has_company or has_company_alias):
        return False

    if any(marker in low for marker in broad_noise) and not (has_symbol or token_hits >= 2 or has_company_alias):
        return False

    return True


def _to_scanx_company_slug(company_name: str | None, symbol: str) -> str | None:
    """Convert company name to a likely ScanX stock-news slug."""
    if not company_name:
        return None

    replacements = {
        "limited": "ltd",
        "ltd": "ltd",
        "incorporated": "inc",
        "corporation": "corp",
        "company": "co",
    }

    tokens = []
    for token in re.findall(r"[a-z0-9]+", company_name.lower()):
        if token == "the":
            continue
        tokens.append(replacements.get(token, token))

    slug = "-".join(tokens).strip("-")
    if not slug:
        return None
    if len(slug) < 5 and symbol:
        return None
    return slug


def _parse_scanx_state(html: str) -> dict:
    """Parse ScanX Angular ng-state JSON payload from HTML."""
    match = re.search(r'<script id="ng-state" type="application/json">(.*?)</script>', html, re.S)
    if not match:
        return {}

    payload = unescape(match.group(1))
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _extract_scanx_entries_from_state(state_obj: dict) -> list[dict]:
    """Extract article dictionaries from ScanX ng-state structure."""
    entries: list[dict] = []

    def add_entry(entry: object):
        if not isinstance(entry, dict):
            return
        if not entry.get("articletitle"):
            return
        entries.append(entry)

    for value in state_obj.values():
        if not isinstance(value, dict):
            continue
        data = value.get("b", {}).get("data", {})
        if not isinstance(data, dict):
            continue

        latest = data.get("latest")
        if isinstance(latest, list):
            for item in latest:
                add_entry(item)
        else:
            add_entry(latest)

        next_items = data.get("next")
        if isinstance(next_items, list):
            for item in next_items:
                add_entry(item)

    return entries


# ── Source 1: ScanX stock-news (primary) ────────────────────────────────────
def _fetch_scanx_news(symbol: str, company_name: str | None = None) -> list[dict]:
    """
    ScanX stock-news pages — primary source for India stock headlines.
    Prioritizes last _SCANX_MAX_AGE_DAYS days, then backfills older ScanX
    items to reach 6-7 headlines when enough history exists.
    """
    symbol_u = symbol.upper().strip()
    company_slug = _to_scanx_company_slug(company_name, symbol_u)

    candidate_slugs: list[str] = []
    for candidate in [company_slug, symbol_u.lower()]:
        if candidate and candidate not in candidate_slugs:
            candidate_slugs.append(candidate)

    if not candidate_slugs:
        return []

    articles: list[dict] = []
    seen_links: set[str] = set()

    for slug in candidate_slugs:
        url = f"{_SCANX_BASE_URL}/stock-news/{slug}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code != 200 or not resp.text:
                continue

            state = _parse_scanx_state(resp.text)
            if not state:
                continue

            entries = _extract_scanx_entries_from_state(state)
            if not entries:
                continue

            for entry in entries:
                title = str(entry.get("articletitle") or "").strip()
                category = str(entry.get("category") or "").strip().strip("/")
                article_slug = str(entry.get("slug") or "").strip().strip("/")
                article_id = entry.get("id")
                published = str(entry.get("pubdate") or "").strip()

                if not title or not category or not article_slug or not article_id:
                    continue
                if not _is_relevant_news_title(title, symbol_u, company_name):
                    continue

                link = f"{_SCANX_BASE_URL}/stock-market-news/{category}/{article_slug}/{article_id}"
                if link in seen_links:
                    continue

                seen_links.add(link)
                articles.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "source": "ScanX",
                })

            if articles:
                break
        except Exception as e:
            logger.warning(f"ScanX news fetch failed for {symbol_u} via slug '{slug}': {e}")

    if not articles:
        return []
    articles = _sort_news_articles(articles)

    recent_articles = [
        item for item in articles
        if _is_recent_news(str(item.get("published") or ""), max_age_days=_SCANX_MAX_AGE_DAYS)
    ]
    older_articles = [item for item in articles if item not in recent_articles]

    target = min(_MAX_NEWS, max(_SCANX_TARGET_MIN_NEWS, len(recent_articles)))
    selected = recent_articles[:target]
    if len(selected) < target:
        selected.extend(older_articles[: target - len(selected)])

    logger.info(
        f"ScanX news: selected={len(selected)} recent={len(recent_articles)} total={len(articles)} for {symbol_u}"
    )
    return _sort_news_articles(selected)


# ── Source 2: Google News RSS (fallback) ─────────────────────────────────────
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
            if not _is_relevant_news_title(title, symbol, company_name):
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
        items = _sort_news_articles(items)
        logger.info(f"Google News RSS: {len(items)} recent articles for {symbol}")
        return items

    except Exception as e:
        logger.warning(f"Google News RSS failed for {symbol}: {e}")
        return []


# ── Source 3: yfinance .news (fallback, works when Yahoo not throttled) ──────
def _fetch_yfinance_news(symbol: str, company_name: str | None = None) -> list[dict]:
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
                title = n.get("title", "").strip()
                if not _is_relevant_news_title(title, symbol, company_name):
                    continue
                items.append({
                    "title":     title,
                    "link":      n.get("link", ""),
                    "published": pub_iso,
                    "source":    n.get("publisher", "Yahoo Finance"),
                })
            items = _sort_news_articles(items)
            logger.info(f"yfinance news: {len(items)} recent articles for {symbol}{suffix}")
            return items
        except Exception as e:
            logger.debug(f"yfinance news failed for {symbol}{suffix}: {e}")
    return []


# ── Main function ─────────────────────────────────────────────────────────────
def _get_news_sync(symbol: str, company_name: str | None = None) -> list[dict]:
    """
    Sync — runs in thread pool.
    1. Try ScanX stock-news (primary)
    2. Try Google News RSS (fallback)
    3. Try yfinance .news (fallback)
    4. Return [] — never raises
    """
    symbol = symbol.upper().strip()

    articles = _fetch_scanx_news(symbol, company_name)
    if articles:
        return _sort_news_articles(articles)

    logger.warning(f"ScanX empty for {symbol}, trying Google News RSS...")
    articles = _fetch_google_news(symbol, company_name)
    if articles:
        return _sort_news_articles(articles)

    logger.warning(f"Google News empty for {symbol}, trying yfinance...")
    articles = _fetch_yfinance_news(symbol, company_name)
    if articles:
        return _sort_news_articles(articles)

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
