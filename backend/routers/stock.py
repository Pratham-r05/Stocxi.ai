"""
routers/stock.py — Stock data endpoints.

Endpoints:
    GET /api/v1/stock/{symbol}            → Overview: price + fundamentals + technicals
    GET /api/v1/stock/{symbol}/financials → Screener: quarterly P&L, BS, CF, shareholding
    GET /api/v1/stock/{symbol}/news       → Recent headlines (ScanX primary)

Caching strategy (from AI_CONTEXT.md):
  Overview   → TTL_PRICE (300s)
  Financials → TTL_FINANCIALS (604800s / 7 days)
  News       → TTL_NEWS (7200s / 2 hrs)

Error handling:
  - Invalid symbol → 404
  - Data source failure → 503 with details
  - Each service wrapped in try/except — partial data served gracefully
"""

import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from cache.redis_client import cache_get, cache_set, TTL_OVERVIEW, TTL_FINANCIALS, TTL_NEWS
from services.yfinance_service import get_price_and_fundamentals, get_history
from services.screener_service import get_financials
from services.technicals_service import calculate_technicals
from services.news_service import get_news
from fetchers import nse_client, bse_client
from services import sentiment_service
from services.announcement_summary_service import summarise_announcements
from services.announcements_service import enrich_announcements_with_pdf_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stock", tags=["Stock Data"])

_LOGO_DOMAIN_OVERRIDES = {
    # Symbol-level website fallbacks when upstream metadata is missing/unreachable.
    "ZOMATO": "zomato.com",
    "ETERNAL": "zomato.com",
    "TCS": "tcs.com",
    "ULTRACEMCO": "ultratechcement.com",
    "DAVANGERE": "davangeresugar.com",
    "RELIANCE": "ril.com",
}

# High-quality vector fallback for domains blocked from backend hosts.
_SIMPLEICONS_SYMBOL_SLUG_OVERRIDES = {
    "TCS": "tcs",
    "ZOMATO": "zomato",
    "ETERNAL": "zomato",
}

_SYMBOL_ALIASES = {
    "ZOMATO": "ETERNAL",
}

_LOGO_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _compute_pb(direct_pb, price, book_value_per_share):
    """Return PB ratio: use direct value if available, else compute price / book_value."""
    if direct_pb is not None:
        return direct_pb
    try:
        if price and book_value_per_share and float(book_value_per_share) > 0:
            return round(float(price) / float(book_value_per_share), 2)
    except Exception:
        pass
    return None


def _compute_eps(direct_eps, screener_eps, price, pe_ratio):
    """Return EPS from source values; fallback to price / PE when available."""
    if direct_eps is not None:
        return direct_eps
    if screener_eps is not None:
        return screener_eps
    try:
        if price and pe_ratio and float(pe_ratio) > 0:
            return round(float(price) / float(pe_ratio), 2)
    except Exception:
        pass
    return None


def _extract_domain(url: str | None) -> str | None:
    """Return normalized domain from URL-like string."""
    if not url:
        return None
    try:
        text = str(url).strip()
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.netloc or parsed.path or "").strip().lower()
        if host.startswith("www."):
            host = host[4:]
        return host if host and "." in host else None
    except Exception:
        return None


def _normalize_website_url(website: str | None) -> str | None:
    """Return normalized website URL with scheme for HTTP fetches."""
    if not website:
        return None
    text = str(website).strip()
    if not text:
        return None
    if text.startswith("//"):
        return f"https:{text}"
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return f"https://{text}"


def _clean_logo_candidate(raw_url: str | None, base_url: str) -> str | None:
    """Normalize and validate candidate image URL extracted from HTML."""
    if not raw_url:
        return None
    text = str(raw_url).strip()
    if not text:
        return None
    low = text.lower()
    if low.startswith(("data:", "javascript:", "mailto:", "#")):
        return None
    return urljoin(base_url, text)


def _size_hint_from_tag(tag) -> int:
    """Extract best size hint from HTML tag attributes for logo ranking."""
    try:
        sizes = str(tag.get("sizes") or "")
        match = re.search(r"(\d{2,4})\s*x\s*(\d{2,4})", sizes)
        if match:
            return max(int(match.group(1)), int(match.group(2)))
    except Exception:
        pass

    best = 0
    for attr in ("width", "height"):
        try:
            value = int(float(str(tag.get(attr) or "0").strip()))
            best = max(best, value)
        except Exception:
            continue
    return best


def _score_logo_candidate(url: str, source: str, size_hint: int = 0) -> int:
    """Score a candidate logo URL to prefer high-quality brand assets over favicons."""
    source_base = {
        "og:logo": 240,
        "logo-img": 210,
        "og:image": 180,
        "twitter:image": 170,
        "apple-touch-icon": 140,
        "mask-icon": 120,
        "icon": 90,
    }
    score = source_base.get(source, 80)

    low = url.lower()
    if "logo" in low:
        score += 35
    if "brand" in low:
        score += 12
    if "favicon" in low:
        score -= 40
    if any(token in low for token in ("sprite", "placeholder", "default")):
        score -= 30

    if ".svg" in low:
        score += 45
    elif any(ext in low for ext in (".png", ".webp", ".jpg", ".jpeg")):
        score += 20
    elif ".ico" in low:
        score -= 25

    score += min(max(size_hint, 0), 512) // 4
    return score


def _extract_best_logo_url(html: str, base_url: str) -> str | None:
    """Parse HTML and return the strongest logo/image candidate URL."""
    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()

    def add_candidate(raw_url: str | None, source: str, size_hint: int = 0):
        url = _clean_logo_candidate(raw_url, base_url)
        if not url or url in seen:
            return
        seen.add(url)
        candidates.append((_score_logo_candidate(url, source, size_hint), url))

    # Prefer explicit social metadata first (usually high-resolution).
    for tag in soup.find_all("meta"):
        prop = str(tag.get("property") or tag.get("name") or "").strip().lower()
        content = tag.get("content")
        if prop in {"og:logo", "twitter:logo"}:
            add_candidate(content, "og:logo", _size_hint_from_tag(tag))
        elif prop in {"og:image", "twitter:image", "twitter:image:src"}:
            source = "og:image" if prop == "og:image" else "twitter:image"
            add_candidate(content, source, _size_hint_from_tag(tag))

    # Apple-touch and icon links are more reliable than basic favicon.ico.
    for tag in soup.find_all("link", href=True):
        rel_raw = tag.get("rel") or []
        rel_text = " ".join(rel_raw) if isinstance(rel_raw, list) else str(rel_raw)
        rel = rel_text.lower()
        href = tag.get("href")
        size_hint = _size_hint_from_tag(tag)
        if "apple-touch-icon" in rel:
            add_candidate(href, "apple-touch-icon", size_hint)
        elif "mask-icon" in rel:
            add_candidate(href, "mask-icon", size_hint)
        elif "icon" in rel:
            add_candidate(href, "icon", size_hint)

    # As a fallback, capture obvious logo images in header/nav.
    for tag in soup.find_all("img", src=True)[:80]:
        id_text = str(tag.get("id") or "")
        class_text = " ".join(tag.get("class") or [])
        alt_text = str(tag.get("alt") or "")
        marker = f"{id_text} {class_text} {alt_text}".lower()
        if "logo" in marker or "brand" in marker:
            add_candidate(tag.get("src"), "logo-img", _size_hint_from_tag(tag))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


async def _resolve_logo_url(symbol: str, website: str | None) -> str | None:
    """Resolve best available high-resolution logo URL for a stock symbol."""
    override_domain = _LOGO_DOMAIN_OVERRIDES.get(symbol)
    normalized = _normalize_website_url(website)

    if not normalized and override_domain:
        normalized = f"https://{override_domain}"

    domain = _extract_domain(normalized) or override_domain
    if not normalized and domain:
        normalized = f"https://{domain}"

    fetch_targets: list[str] = []
    if normalized:
        fetch_targets.append(normalized)
    if domain:
        fetch_targets.extend([f"https://{domain}", f"http://{domain}"])

    # Preserve order while deduplicating URL attempts.
    deduped_targets = list(dict.fromkeys(fetch_targets))

    if deduped_targets:
        timeout = httpx.Timeout(8.0, connect=4.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=_LOGO_FETCH_HEADERS,
        ) as client:
            for target in deduped_targets:
                try:
                    resp = await client.get(target)
                    if resp.status_code >= 400:
                        continue
                    content_type = (resp.headers.get("content-type") or "").lower()
                    body = resp.text or ""
                    if "text/html" not in content_type and "<html" not in body[:1000].lower():
                        continue
                    best = _extract_best_logo_url(body, str(resp.url))
                    if best:
                        return best
                except Exception as e:
                    logger.debug(f"Logo discovery failed for {symbol} on {target}: {e}")

            # If metadata/logo image isn't exposed in HTML, probe common app/icon paths.
            if domain:
                static_icon_paths = [
                    "/apple-touch-icon.png",
                    "/android-chrome-512x512.png",
                    "/android-chrome-192x192.png",
                    "/apple-touch-icon-precomposed.png",
                    "/favicon-96x96.png",
                    "/favicon-32x32.png",
                ]
                for path in static_icon_paths:
                    for scheme in ("https", "http"):
                        candidate = f"{scheme}://{domain}{path}"
                        try:
                            resp = await client.get(candidate)
                            if resp.status_code >= 400:
                                continue
                            content_type = (resp.headers.get("content-type") or "").lower()
                            if content_type.startswith("image/"):
                                return str(resp.url)
                        except Exception:
                            continue

    simpleicons_slug = _SIMPLEICONS_SYMBOL_SLUG_OVERRIDES.get(symbol)
    if simpleicons_slug:
        return f"https://cdn.simpleicons.org/{simpleicons_slug}"

    # Last fallback: still return something predictable instead of null.
    if domain:
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=256"
    return None


# ── GET /api/v1/stock/{symbol} ────────────────────────────────────────────────
@router.get("/{symbol}")
async def get_stock_overview(symbol: str):
    """
    Stock overview — price, fundamentals, technicals, key screener ratios.

    Merges data from:
      - nsepython (price, 52W, change)
      - Screener.in #top-ratios (PE, market cap, book value, ROCE, ROE)
      - technicals_service (RSI, MACD, ADX, BB, EMA)

    Cached 5 minutes (price changes frequently).
    """
    requested_symbol = symbol.upper().strip()
    symbol = _SYMBOL_ALIASES.get(requested_symbol, requested_symbol)
    cache_key = f"stock:overview:v8:{requested_symbol}"

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = await cache_get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return JSONResponse(content=cached)

    # ── Fetch price + fundamentals (required — 404 if not found) ──────────────
    try:
        price_data = await get_price_and_fundamentals(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Price fetch failed for {symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Price data unavailable: {e}")

    # ── Fetch screener ratios (optional — degrade gracefully) ─────────────────
    screener_data = {}
    screener_ratios = {}
    screener_website = None
    try:
        screener_data  = await get_financials(symbol)
        screener_ratios = screener_data.get("ratios", {})
        screener_website = screener_data.get("website")
    except Exception as e:
        logger.warning(f"Screener ratios failed for {symbol}: {e}")

    bse_meta = {}
    try:
        bse_meta = await bse_client.fetch_meta_info(symbol)
    except Exception as e:
        logger.debug(f"BSE meta ratios failed for {symbol}: {e}")

    # ── Fetch technicals (optional — degrade gracefully) ─────────────────────
    technicals = {}
    try:
        technicals = await calculate_technicals(symbol)
    except Exception as e:
        logger.warning(f"Technicals failed for {symbol}: {e}")

    # ── Merge: screener enriches the price_data where values are None ─────────
    def fill(primary, fallback_key):
        """Use screener value if primary source returned None."""
        return primary if primary is not None else screener_ratios.get(fallback_key)

    def latest_row_value(table: dict, *labels: str) -> float | None:
        for row in table.get("rows", []):
            label = str(row.get("label") or "").lower()
            if not any(token in label for token in labels):
                continue
            for raw in reversed(row.get("values", [])):
                try:
                    val = float(str(raw).replace(",", "").replace("%", "").strip())
                    if val == val:
                        return val
                except (TypeError, ValueError):
                    continue
        return None

    quarterly_table = screener_data.get("quarterly_results", {}) if isinstance(screener_data, dict) else {}
    opm_value = bse_meta.get("opm") or latest_row_value(quarterly_table, "opm", "financing margin")
    if opm_value is None:
        revenue_latest = latest_row_value(quarterly_table, "sales", "revenue")
        operating_profit_latest = latest_row_value(quarterly_table, "operating profit", "financing profit")
        if revenue_latest and operating_profit_latest is not None:
            opm_value = round(operating_profit_latest / revenue_latest * 100, 1)
    npm_value = bse_meta.get("npm")
    if npm_value is None:
        sales_latest = latest_row_value(quarterly_table, "sales", "revenue")
        profit_latest = latest_row_value(quarterly_table, "net profit")
        if sales_latest and profit_latest is not None:
            npm_value = round(profit_latest / sales_latest * 100, 1)

    company_website = price_data.get("website") or screener_website
    if not company_website:
        fallback_domain = _LOGO_DOMAIN_OVERRIDES.get(requested_symbol) or _LOGO_DOMAIN_OVERRIDES.get(symbol)
        if fallback_domain:
            company_website = f"https://{fallback_domain}"

    logo_cache_key = f"stock:logo:v4:{requested_symbol}"
    logo_url = None
    cached_logo = await cache_get(logo_cache_key)
    if isinstance(cached_logo, dict) and "logo_url" in cached_logo:
        logo_url = cached_logo.get("logo_url")
    else:
        logo_url = await _resolve_logo_url(requested_symbol, company_website)
        await cache_set(logo_cache_key, {"logo_url": logo_url}, TTL_FINANCIALS)

    response = {
        "symbol":          requested_symbol,
        "canonical_symbol": symbol,
        "exchange":        price_data.get("exchange"),
        "company_name":    price_data.get("company_name") or requested_symbol,
        "company_website": company_website,
        "logo_url":        logo_url,
        "sector":          fill(price_data.get("sector"),         "sector"),
        "industry":        fill(price_data.get("industry"),       "industry"),
        # ── Price ──────────────────────────────────────────────────────────────
        "price":           price_data.get("price"),
        "previous_close":  price_data.get("previous_close"),
        "change":          price_data.get("change"),
        "change_percent":  price_data.get("change_percent"),
        "open":            price_data.get("open"),
        "day_high":        price_data.get("day_high"),
        "day_low":         price_data.get("day_low"),
        "week_52_high":    price_data.get("week_52_high"),
        "week_52_low":     price_data.get("week_52_low"),
        "volume":          price_data.get("volume"),
        # ── Fundamentals (price_data first, screener fallback) ─────────────────
        "market_cap":      fill(price_data.get("market_cap"),     "market_cap"),
        "pe_ratio":        fill(price_data.get("pe_ratio"),       "pe_ratio"),
        "pb_ratio":        _compute_pb(
                               price_data.get("pb_ratio"),
                               price_data.get("price"),
                               screener_ratios.get("book_value"),
                           ),
        "book_value":      screener_ratios.get("book_value"),
        "eps":             _compute_eps(
                               price_data.get("eps"),
                               screener_ratios.get("eps"),
                               price_data.get("price"),
                               fill(price_data.get("pe_ratio"), "pe_ratio"),
                           ),
        "dividend_yield":  fill(price_data.get("dividend_yield"), "dividend_yield"),
        "beta":            price_data.get("beta"),
        "roce":            screener_ratios.get("roce"),
        "roe":             screener_ratios.get("roe"),
        "operating_margin": opm_value,
        "net_profit_margin": npm_value,
        "face_value":      screener_ratios.get("face_value"),
        "debt_to_equity":  screener_ratios.get("debt_to_equity"),
        "current_ratio":   screener_ratios.get("current_ratio"),
        # ── Technicals ─────────────────────────────────────────────────────────
        "technicals": {
            "rsi":              technicals.get("rsi"),
            "rsi_signal":       technicals.get("rsi_signal") or "Neutral",
            "macd":             technicals.get("macd"),
            "macd_signal_line": technicals.get("macd_signal_line"),
            "macd_histogram":   technicals.get("macd_histogram"),
            "macd_signal":      technicals.get("macd_signal") or "Neutral",
            "adx":              technicals.get("adx"),
            "adx_signal":       technicals.get("adx_signal") or "Weak Trend",
            "atr":              technicals.get("atr"),
            "bb_upper":         technicals.get("bb_upper"),
            "bb_lower":         technicals.get("bb_lower"),
            "bb_signal":        technicals.get("bb_signal") or "Inside Bands",
            "ema_20":           technicals.get("ema_20"),
            "ema_50":           technicals.get("ema_50"),
            "ema_200":          technicals.get("ema_200"),
            "ema_signal":       technicals.get("ema_signal") or "Mixed",
            "stoch_k":          technicals.get("stoch_k"),
            "stoch_d":          technicals.get("stoch_d"),
            "stoch_signal":     technicals.get("stoch_signal") or "Neutral",
            "vwap":             technicals.get("vwap"),
            "vwap_signal":      technicals.get("vwap_signal") or "Neutral",
            "obv":              technicals.get("obv"),
            "obv_signal":       technicals.get("obv_signal") or "Neutral",
            "volume_sma_20":    technicals.get("volume_sma_20"),
            "overall_signal":   technicals.get("overall_signal") or "Neutral",
        },
    }

    # ── Fetch sentiment (optional — never blocks overview) ────────────────────
    sentiment = None
    try:
        sentiment = await sentiment_service.get_sentiment(symbol)
    except Exception as e:
        logger.warning(f"Sentiment fetch failed for {symbol}: {e}")

    response["sentiment"] = sentiment

    await cache_set(cache_key, response, TTL_OVERVIEW)
    return JSONResponse(content=response)


# ── GET /api/v1/stock/{symbol}/financials ─────────────────────────────────────
@router.get("/{symbol}/financials")
async def get_stock_financials(symbol: str):
    """
    Screener.in financial tables:
      - quarterly_results (P&L)
      - balance_sheet
      - cash_flow
      - shareholding

    Cached 7 days — updates only on quarterly results.
    """
    symbol = symbol.upper().strip()
    # Versioned key to invalidate older cached payloads after schema/parser upgrades.
    cache_key = f"stock:financials:v3:{symbol}"

    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached)

    try:
        data = await get_financials(symbol)
    except Exception as e:
        logger.error(f"Financials fetch failed for {symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Financial data unavailable: {e}")

    if not data.get("quarterly_results"):
        raise HTTPException(
            status_code=404,
            detail=f"No financial data found for '{symbol}'. Check the symbol."
        )

    response = {
        "symbol":            symbol,
        "source_url":        data.get("source_url"),
        "quarterly_results": data.get("quarterly_results", {}),
        "annual_results":    data.get("annual_results", {}),
        "balance_sheet":     data.get("balance_sheet", {}),
        "cash_flow":         data.get("cash_flow", {}),
        "shareholding":      data.get("shareholding", {}),
        "mf_holdings":       data.get("mf_holdings", {}),
        "mf_holdings_source_status": (
            "available"
            if len((data.get("mf_holdings", {}) or {}).get("rows", [])) > 0
            else "not_available"
        ),
        "mf_holdings_note": (
            "Mutual fund investor holdings are available from Screener investor data."
            if len((data.get("mf_holdings", {}) or {}).get("rows", [])) > 0
            else "No mutual fund investor rows found in source data for this symbol."
        ),
    }

    await cache_set(cache_key, response, TTL_FINANCIALS)
    return JSONResponse(content=response)


# ── GET /api/v1/stock/{symbol}/news ───────────────────────────────────────────
@router.get("/{symbol}/news")
async def get_stock_news(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=20, description="Number of articles (1-20)"),
):
    """
    Recent news headlines from ScanX (primary) with Google/yfinance fallback.
    Returns [{title, link, published, source}, ...]
    Cached 2 hours.
    """
    symbol = symbol.upper().strip()
    cache_key = f"stock:news:v7:{symbol}"  # v7: stronger company-alias relevance + strict 4-day recency

    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached)

    company_name = None
    overview_cache_key = f"stock:overview:v5:{symbol}"
    cached_overview = await cache_get(overview_cache_key)
    if isinstance(cached_overview, dict):
        company_name = cached_overview.get("company_name")

    if not company_name:
        try:
            price_data = await get_price_and_fundamentals(symbol)
            company_name = price_data.get("company_name")
        except Exception:
            company_name = None

    try:
        articles = await get_news(symbol, company_name=company_name)
    except Exception as e:
        logger.error(f"News fetch failed for {symbol}: {e}")
        articles = []

    response = {
        "symbol":   symbol,
        "count":    len(articles[:limit]),
        "articles": articles[:limit],
    }

    if articles:
        await cache_set(cache_key, response, TTL_NEWS)

    return JSONResponse(content=response)


# ── GET /api/v1/stock/{symbol}/sentiment ─────────────────────────────────────
@router.get("/{symbol}/sentiment")
async def get_stock_sentiment(
    symbol: str,
    refresh: bool = Query(default=False, description="If true, bypass cache and fetch fresh social data"),
):
    """
    Reddit + X/Twitter social sentiment for a stock symbol.
    Returns combined dict with Reddit posts, Twitter posts, signals, and 7-day chart data.
    Cached 1 hour.
    """
    # returns Reddit + Twitter sentiment for symbol
    return await sentiment_service.get_sentiment(symbol.upper().strip(), force_refresh=refresh)


# ── GET /api/v1/stock/{symbol}/history ───────────────────────────────────────
@router.get("/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period: str = Query(default="1y", description="Period: 1d, 1w, 1mo, 3mo, 6mo, 1y, 2y, 5y"),
):
    """
    Daily closing prices for charting.
    Returns { symbol, period, closes: [{date, close}, ...] }
    Cached 1 hour (same as sentiment TTL).
    """
    symbol = symbol.upper().strip()
    # v5: strict period bucketing (1D=1m, 1W=1h, 1M=12h, 1Y=1d)
    cache_key = f"stock:history:v5:{symbol}:{period}"
    ttl = 300 if period in {"1d", "1w"} else TTL_NEWS  # 5min for intraday, 1hr for rest

    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached)

    response = await get_history(symbol, period)
    if response.get("closes"):
        await cache_set(cache_key, response, ttl)

    return JSONResponse(content=response)


# ── GET /api/v1/stock/{symbol}/announcements ──────────────────────────────────
def _announcement_url_fields(raw_url: str) -> tuple[str, str]:
    """Return (pdf_url, filing_url) without mislabeling non-PDF files."""
    url = str(raw_url or "").strip()
    if not url:
        return "", ""
    if url.lower().endswith(".pdf"):
        return url, ""
    return "", url


def _normalise_announcement_date(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _announcement_sort_date(raw: str) -> datetime:
    text = str(raw or "").strip()
    if not text:
        return datetime.min
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.min


@router.get("/{symbol}/announcements")
async def get_stock_announcements(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=50, description="Number of announcements (1-50)"),
):
    """
    Corporate announcements from NSE + BSE for a stock.
    Merges: NSE announcements, board meetings, actions + BSE actions.
    Cached 2 hours.
    """
    symbol = symbol.upper().strip()
    cache_key = f"stock:announcements:v11:{symbol}"

    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached)

    # Fetch from NSE and BSE concurrently
    results = await asyncio.gather(
        nse_client.fetch_announcements(symbol, limit=limit),
        nse_client.fetch_board_meetings(symbol),
        nse_client.fetch_actions(symbol),
        bse_client.fetch_announcements(symbol, limit=limit),
        bse_client.fetch_actions(symbol),
        return_exceptions=True,
    )

    nse_ann_res, nse_meetings_res, nse_actions_res, bse_ann_res, bse_actions_res = results

    all_items: list[dict] = []

    # NSE announcements (regulatory filings, exchange notices)
    if isinstance(nse_ann_res, dict):
        for item in nse_ann_res.get("items", []):
            pdf_url, filing_url = _announcement_url_fields(item.get("pdf_url") or "")
            all_items.append({
                "subject":  item.get("title") or item.get("category") or "NSE Filing",
                "date":     _normalise_announcement_date(item.get("date", "")),
                "category": "NSE Filing",
                "pdf_url":  pdf_url,
                "filing_url": filing_url,
                "details":  item.get("details") or item.get("category") or "",
                "source":   "NSE",
            })

    # NSE board meetings
    if isinstance(nse_meetings_res, dict):
        for m in nse_meetings_res.get("meetings", []):
            pdf_url, filing_url = _announcement_url_fields(m.get("pdf_url") or "")
            all_items.append({
                "subject":  m.get("purpose") or "Board Meeting",
                "date":     _normalise_announcement_date(m.get("date", "")),
                "category": "Board Meeting",
                "pdf_url":  pdf_url,
                "filing_url": filing_url,
                "details":  m.get("purpose") or "",
                "source":   "NSE",
            })

    # NSE corporate actions (dividends, bonus, splits)
    if isinstance(nse_actions_res, dict):
        for a in nse_actions_res.get("actions", []):
            all_items.append({
                "subject":  a.get("purpose") or a.get("subject") or "Corporate Action",
                "date":     _normalise_announcement_date(a.get("ex_date") or a.get("record_date") or ""),
                "category": "Corporate Action",
                "pdf_url":  "",
                "filing_url": "",
                "details":  a.get("details") or "",
                "source":   "NSE",
            })

    # BSE announcements (filings with exchange attachment links)
    if isinstance(bse_ann_res, dict):
        for item in bse_ann_res.get("items", []):
            pdf_url, filing_url = _announcement_url_fields(
                item.get("pdf_url") or item.get("filing_url") or ""
            )
            all_items.append({
                "subject":  item.get("title") or item.get("category") or "BSE Filing",
                "date":     _normalise_announcement_date(item.get("date", "")),
                "category": item.get("category") or "BSE Filing",
                "pdf_url":  pdf_url,
                "filing_url": filing_url,
                "details":  item.get("details") or "",
                "source":   "BSE",
            })

    # BSE corporate actions
    if isinstance(bse_actions_res, dict):
        for a in bse_actions_res.get("actions", []):
            all_items.append({
                "subject":  a.get("purpose") or "Corporate Action",
                "date":     _normalise_announcement_date(a.get("ex_date") or a.get("record_date") or ""),
                "category": "Corporate Action",
                "pdf_url":  "",
                "filing_url": "",
                "details":  a.get("details") or "",
                "source":   "BSE",
            })

    def _sort_key(item: dict) -> datetime:
        return _announcement_sort_date(item.get("date") or "")

    all_items = [item for item in all_items if item.get("pdf_url")]
    all_items.sort(key=_sort_key, reverse=True)

    seen: set[tuple] = set()
    unique: list[dict] = []
    for item in all_items:
        key = (item.get("date", ""), item.get("subject", "")[:60].lower(), item.get("source", ""))
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique = [it for it in unique if it.get("subject") and it.get("date")][:10]

    # Gemini Flash: add a 1-sentence investor-relevant summary for each item
    if unique:
        unique = await enrich_announcements_with_pdf_text(unique)
        unique = [it for it in unique if it.get("pdf_url")]
        unique = await summarise_announcements(symbol, unique)

    for item in unique:
        summary = str(item.get("summary") or "").strip()
        if not summary:
            item["summary"] = str(item.get("subject") or "").strip()[:120]

    response = {
        "symbol":        symbol,
        "count":         len(unique),
        "announcements": unique,
    }

    if unique:
        await cache_set(cache_key, response, TTL_NEWS)

    return JSONResponse(content=response)
