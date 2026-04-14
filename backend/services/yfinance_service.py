"""
yfinance_service.py — Price + fundamental data for Indian stocks.

Why we stopped using yfinance for quotes:
  Yahoo Finance IP-blocks the crumb endpoint (/v1/test/getcrumb) during
  heavy testing. All quoteSummary calls fail with 429 even with retries.

New stack:
  Primary  → nsepython.nse_eq(symbol)
             Hits NSE India's public API directly — no Yahoo, no rate limits.
             Works for all NSE-listed stocks (most Indian large/mid caps).

  Fallback → Direct httpx GET to Yahoo Finance chart API
             /v8/finance/chart/{symbol}.BO — chart endpoint does NOT need crumb.
             Used only for BSE-only stocks not listed on NSE.

  yfinance → Still kept in requirements for technicals_service.py which
             downloads historical OHLCV via yf.download() (different endpoint).
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ── NSE primary: nsepython ─────────────────────────────────────────────────────
def _fetch_from_nse(symbol: str) -> dict:
    """
    Sync — run in thread pool.
    nsepython.nse_eq() calls NSE India's public quote API directly.
    Returns structured data or raises on failure.
    """
    # Import here so startup doesn't fail if package has issues
    from nsepython import nse_eq  # type: ignore

    symbol = symbol.upper().strip()
    raw = nse_eq(symbol)  # raises if symbol not found on NSE

    price_info  = raw.get("priceInfo", {})
    metadata    = raw.get("metadata", {})
    info        = raw.get("info", {})          # NSE also puts companyName here
    trade_info  = raw.get("tradeInfo", {})
    sec_info    = raw.get("securityInfo", {})
    intraday    = price_info.get("intraDayHighLow", {})
    week_hl     = price_info.get("weekHighLow", {})

    price = price_info.get("lastPrice") or price_info.get("close")
    if not price or float(price) <= 0:
        raise ValueError(f"NSE returned no price for {symbol}")

    previous_close = price_info.get("previousClose") or price
    change         = price_info.get("change", round(float(price) - float(previous_close), 2))
    change_pct     = price_info.get("pChange", 0.0)

    # Market cap from tradeInfo (in crores) → convert to absolute value
    market_cap_cr = trade_info.get("totalMarketCap")
    market_cap = int(market_cap_cr * 1e7) if market_cap_cr else None  # crores → rupees

    # Company name: metadata.companyName exists but can return ticker for some stocks.
    # Try info.companyName as a second source before falling back to symbol.
    company_name = (
        metadata.get("companyName") or
        info.get("companyName") or
        symbol
    )

    return {
        "exchange":        "NSE",
        "company_name":    company_name,
        "industry":        metadata.get("industry"),
        "sector":          None,  # NSE API doesn't give sector; screener.in does
        "price":           round(float(price), 2),
        "previous_close":  round(float(previous_close), 2),
        "change":          round(float(change), 2),
        "change_percent":  round(float(change_pct), 2),
        "open":            price_info.get("open"),
        "day_high":        intraday.get("max"),
        "day_low":         intraday.get("min"),
        "week_52_high":    week_hl.get("max"),
        "week_52_low":     week_hl.get("min"),
        "volume":          trade_info.get("totalTradedVolume"),
        "market_cap":      market_cap,
        # fundamentals NSE doesn't expose via this endpoint:
        "pe_ratio":        None,
        "pb_ratio":        None,
        "eps":             None,
        "dividend_yield":  None,
        "beta":            None,
        "description":     None,
        "website":         None,
        "employees":       None,
    }


# ── BSE fallback: Yahoo chart API (no crumb needed) ───────────────────────────
async def _fetch_from_yahoo_chart(symbol: str) -> dict:
    """
    Async httpx call to Yahoo Finance chart endpoint.
    /v8/finance/chart/ does NOT require a crumb — different auth flow.
    Used as fallback for BSE-only stocks.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.yahoo.com",
        "Accept": "application/json",
    }

    for suffix, exchange in [(".NS", "NSE"), (".BO", "BSE")]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}{suffix}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            result = (data.get("chart") or {}).get("result") or []
            if not result:
                continue

            meta  = result[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            if not price or float(price) <= 0:
                continue

            prev  = meta.get("previousClose") or price
            logger.info(f"Yahoo chart API: got price for {symbol} on {exchange}")
            return {
                "exchange":        exchange,
                "company_name":    meta.get("shortName") or symbol,
                "industry":        None,
                "sector":          None,
                "price":           round(float(price), 2),
                "previous_close":  round(float(prev), 2),
                "change":          round(float(price) - float(prev), 2),
                "change_percent":  round(((float(price) - float(prev)) / float(prev)) * 100, 2),
                "open":            meta.get("regularMarketOpen"),
                "day_high":        meta.get("regularMarketDayHigh"),
                "day_low":         meta.get("regularMarketDayLow"),
                "week_52_high":    meta.get("fiftyTwoWeekHigh"),
                "week_52_low":     meta.get("fiftyTwoWeekLow"),
                "volume":          meta.get("regularMarketVolume"),
                "market_cap":      meta.get("marketCap"),
                "pe_ratio":        None,
                "pb_ratio":        None,
                "eps":             None,
                "dividend_yield":  None,
                "beta":            None,
                "description":     None,
                "website":         None,
                "employees":       None,
            }
        except Exception as e:
            logger.warning(f"Yahoo chart fallback failed for {symbol}{suffix}: {e}")
            continue

    raise ValueError(f"Symbol '{symbol}' not found on NSE or BSE")


async def get_price_and_fundamentals(symbol: str) -> dict:
    """
    Async entry point for all services.
    Flow:
      1. Try NSE via nsepython (direct NSE API, fastest, no rate limits)
      2. If NSE fails → try Yahoo chart API (no crumb, works for BSE stocks)
      3. If both fail → raise ValueError

    The result always has the same keys — some may be None if source
    doesn't provide them (frontend shows "—" for null fields).
    """
    symbol = symbol.upper().strip()

    # Stage 1: NSE direct
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _fetch_from_nse, symbol)
        data["symbol"] = symbol          # ← add symbol key
        logger.info(f"Quote source: NSE direct for {symbol}")
        return data
    except Exception as e:
        logger.warning(f"NSE direct failed for {symbol}: {e}. Trying Yahoo chart...")

    # Stage 2: Yahoo chart API (BSE fallback)
    data = await _fetch_from_yahoo_chart(symbol)
    data["symbol"] = symbol              # ← add symbol key
    return data
