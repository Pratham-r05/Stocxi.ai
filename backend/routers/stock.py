"""
routers/stock.py — Stock data endpoints.

Endpoints:
  GET /api/v1/stock/{symbol}            → Overview: price + fundamentals + technicals
  GET /api/v1/stock/{symbol}/financials → Screener: quarterly P&L, BS, CF, shareholding
  GET /api/v1/stock/{symbol}/news       → Recent headlines (Google News RSS)

Caching strategy (from AI_CONTEXT.md):
  Overview   → TTL_PRICE (300s)
  Financials → TTL_FINANCIALS (604800s / 7 days)
  News       → TTL_NEWS (7200s / 2 hrs)

Error handling:
  - Invalid symbol → 404
  - Data source failure → 503 with details
  - Each service wrapped in try/except — partial data served gracefully
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from cache.redis_client import cache_get, cache_set, TTL_OVERVIEW, TTL_FINANCIALS, TTL_NEWS
from services.yfinance_service import get_price_and_fundamentals
from services.screener_service import get_financials
from services.technicals_service import calculate_technicals
from services.news_service import get_news
from services.announcements_service import get_announcements

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stock", tags=["Stock Data"])


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
    symbol = symbol.upper().strip()
    cache_key = f"stock:overview:{symbol}"

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
    screener_ratios = {}
    try:
        screener_data  = await get_financials(symbol)
        screener_ratios = screener_data.get("ratios", {})
    except Exception as e:
        logger.warning(f"Screener ratios failed for {symbol}: {e}")

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

    response = {
        "symbol":          symbol,
        "exchange":        price_data.get("exchange"),
        "company_name":    price_data.get("company_name") or symbol,
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
        "pb_ratio":        fill(price_data.get("pb_ratio"),       None),
        "book_value":      screener_ratios.get("book_value"),
        "eps":             price_data.get("eps"),
        "dividend_yield":  fill(price_data.get("dividend_yield"), "dividend_yield"),
        "beta":            price_data.get("beta"),
        "roce":            screener_ratios.get("roce"),
        "roe":             screener_ratios.get("roe"),
        "face_value":      screener_ratios.get("face_value"),
        # ── Technicals ─────────────────────────────────────────────────────────
        "technicals": {
            "rsi":              technicals.get("rsi"),
            "rsi_signal":       technicals.get("rsi_signal", "Unknown"),
            "macd":             technicals.get("macd"),
            "macd_signal":      technicals.get("macd_signal", "Unknown"),
            "adx":              technicals.get("adx"),
            "adx_signal":       technicals.get("adx_signal", "Unknown"),
            "atr":              technicals.get("atr"),
            "bb_upper":         technicals.get("bb_upper"),
            "bb_lower":         technicals.get("bb_lower"),
            "bb_signal":        technicals.get("bb_signal", "Unknown"),
            "ema_20":           technicals.get("ema_20"),
            "ema_50":           technicals.get("ema_50"),
            "ema_200":          technicals.get("ema_200"),
            "ema_signal":       technicals.get("ema_signal", "Unknown"),
            "volume_sma_20":    technicals.get("volume_sma_20"),
            "overall_signal":   technicals.get("overall_signal", "Unknown"),
        },
    }

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
    Recent news headlines from Google News RSS.
    Returns [{title, link, published, source}, ...]
    Cached 2 hours.
    """
    symbol = symbol.upper().strip()
    cache_key = f"stock:news:{symbol}"

    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached)

    try:
        articles = await get_news(symbol)
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


# ── GET /api/v1/stock/{symbol}/announcements ──────────────────────────────────
@router.get("/{symbol}/announcements")
async def get_stock_announcements(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=20, description="Number of announcements (1-20)"),
):
    """
    Recent BSE corporate announcements for a stock.
    Source: BSE India public API (free, no auth required).
    Returns [{subject, date, category, pdf_url, bse_code}, ...]
    Cached 2 hours.
    """
    symbol = symbol.upper().strip()
    cache_key = f"stock:announcements:{symbol}"

    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached)

    try:
        items = await get_announcements(symbol, limit=limit)
    except Exception as e:
        logger.error(f"Announcements fetch failed for {symbol}: {e}")
        items = []

    response = {
        "symbol":        symbol,
        "count":         len(items),
        "announcements": [
            {
                **item,
                "title": item.get("subject", "No subject"),
            }
            for item in items
        ],
    }

    if items:
        await cache_set(cache_key, response, TTL_NEWS)  # reuse 2hr TTL

    return JSONResponse(content=response)
