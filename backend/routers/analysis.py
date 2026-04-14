"""
routers/analysis.py — AI-powered stock analysis endpoint.

Endpoint:
  GET /api/v1/analysis/{symbol}?risk_level=medium

Flow:
  1. Fetch price + fundamentals (required)
  2. Fetch screener ratios (optional, enriches fundamentals)
  3. Fetch technicals (optional, enriches analysis)
  4. Fetch news (optional, informs sentiment)
  5. Run all fetches concurrently via asyncio.gather()
  6. Call AI service with merged data
  7. Cache result 6 hours

Cache TTL: 21600s (6 hrs) — from AI_CONTEXT.md TTL_ANALYSIS
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from cache.redis_client import cache_get, cache_set, TTL_ANALYSIS
from services.yfinance_service import get_price_and_fundamentals
from services.screener_service import get_financials
from services.technicals_service import calculate_technicals
from services.news_service import get_news
from services.ai_service import analyse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["AI Analysis"])


@router.get("/{symbol}")
async def get_analysis(
    symbol: str,
    risk_level: str = Query(
        default="medium",
        pattern="^(low|medium|high)$",
        description="Investor risk profile: low | medium | high",
    ),
):
    """
    AI-powered stock analysis for the given symbol and risk level.

    Returns structured assessment:
      - fundamentals verdict (Strong / Weak / Neutral)
      - technicals verdict (Bullish / Bearish / Mixed)
      - news sentiment (Positive / Negative / Neutral)
      - final_verdict (BUY / HOLD / AVOID)
      - plain_english summary tailored to risk level
      - risk_match (bool — does this stock suit the investor's risk profile?)
      - SEBI disclaimer

    Cached 6 hours per symbol+risk_level combination.
    """
    symbol     = symbol.upper().strip()
    risk_level = risk_level.lower().strip()
    cache_key  = f"analysis:{symbol}:{risk_level}"

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = await cache_get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return JSONResponse(content=cached)

    # ── Step 1: Price (required) — fail fast if symbol invalid ────────────────
    try:
        price_data = await get_price_and_fundamentals(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Price fetch failed for {symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Price data unavailable: {e}")

    # ── Step 2: Concurrent fetch of optional data ─────────────────────────────
    # All three run in parallel — total wait = slowest (usually technicals ~5s)
    screener_task   = get_financials(symbol)
    technicals_task = calculate_technicals(symbol)
    news_task       = get_news(symbol, price_data.get("company_name"))

    screener_result, technicals_result, news_result = await asyncio.gather(
        screener_task, technicals_task, news_task,
        return_exceptions=True,  # never let one failure kill the others
    )

    # ── Step 3: Safely unpack results (may be exceptions) ─────────────────────
    screener_ratios = {}
    if isinstance(screener_result, dict):
        screener_ratios = screener_result.get("ratios", {})
    else:
        logger.warning(f"Screener failed for {symbol}: {screener_result}")

    technicals = {}
    if isinstance(technicals_result, dict):
        technicals = technicals_result
    else:
        logger.warning(f"Technicals failed for {symbol}: {technicals_result}")

    news = []
    if isinstance(news_result, list):
        news = news_result
    else:
        logger.warning(f"News failed for {symbol}: {news_result}")

    # ── Step 4: Build merged fundamentals dict for AI prompt ─────────────────
    def fill(primary_val, screener_key):
        return primary_val if primary_val is not None else screener_ratios.get(screener_key)

    fundamentals_for_ai = {
        "price":          price_data.get("price"),
        "pe_ratio":       fill(price_data.get("pe_ratio"),       "pe_ratio"),
        "market_cap":     fill(price_data.get("market_cap"),     "market_cap"),
        "book_value":     fill(price_data.get("pb_ratio"),       "book_value"),
        "week_52_high":   price_data.get("week_52_high"),
        "week_52_low":    price_data.get("week_52_low"),
        "dividend_yield": fill(price_data.get("dividend_yield"), "dividend_yield"),
        "roce":           screener_ratios.get("roce"),
        "roe":            screener_ratios.get("roe"),
        "eps":            price_data.get("eps"),
        "beta":           price_data.get("beta"),
        "change_percent": price_data.get("change_percent"),
    }

    # ── Step 5: AI analysis ───────────────────────────────────────────────────
    ai_result = await analyse(
        symbol=symbol,
        fundamentals=fundamentals_for_ai,
        technicals=technicals,
        news=news,
        risk_level=risk_level,
    )

    # ── Step 6: Enrich response with source data ──────────────────────────────
    response = {
        **ai_result,
        "company_name":   price_data.get("company_name") or symbol,
        "exchange":       price_data.get("exchange"),
        "current_price":  price_data.get("price"),
        "change_percent": price_data.get("change_percent"),
        "overall_technical_signal": technicals.get("overall_signal", "Unknown"),
    }

    # Cache only if AI didn't error
    if not ai_result.get("error"):
        await cache_set(cache_key, response, TTL_ANALYSIS)

    return JSONResponse(content=response)
