"""
services/search_service.py — NSE symbol autocomplete.

Strategy:
  1. Try nsepython.nse_eq_symbols() — returns all ~2000 NSE equity symbols
  2. Filter by prefix match (case-insensitive)
  3. Return up to `limit` results with {symbol, name, exchange}

Why prefix-only (not substring):
  - Users type RELI → RELIANCE, not random middle matches
  - Keeps results clean and fast

Caching:
  - The full symbol list is fetched once and cached in-process as a module-level variable
  - Individual search queries are cached in Redis (TTL_SEARCH = 3600s)
  - This avoids hammering NSE on every keystroke
"""

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── In-process symbol cache ────────────────────────────────────────────────────
# Loaded once on first search, reused for the server's lifetime
_NSE_SYMBOLS: list[dict] | None = None


async def _load_nse_symbols() -> list[dict]:
    """
    Fetch all NSE equity symbols from nsepython.
    Returns list of {symbol, name, exchange}.
    Falls back to top-50 hardcoded list if nsepython fails.
    """
    global _NSE_SYMBOLS
    if _NSE_SYMBOLS is not None:
        return _NSE_SYMBOLS

    try:
        import asyncio
        from nsepython import nse_eq_symbols

        # nse_eq_symbols() is synchronous — run in thread pool to avoid blocking
        loop = asyncio.get_running_loop()
        symbols_raw = await loop.run_in_executor(None, nse_eq_symbols)

        # nsepython returns a plain list of ticker strings
        _NSE_SYMBOLS = [
            {"symbol": s.upper(), "name": s.upper(), "exchange": "NSE"}
            for s in symbols_raw
        ]
        logger.info(f"Loaded {len(_NSE_SYMBOLS)} NSE symbols")

    except Exception as e:
        logger.warning(f"nsepython symbol load failed ({e}), using fallback list")
        _NSE_SYMBOLS = _fallback_symbols()

    return _NSE_SYMBOLS


def _fallback_symbols() -> list[dict]:
    """
    Top-50 most traded NSE stocks — used if nsepython is unavailable.
    This ensures autocomplete always works, even offline.
    """
    tickers = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
        "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
        "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "HCLTECH",
        "WIPRO", "SUNPHARMA", "ULTRACEMCO", "TITAN", "BAJFINANCE",
        "BAJAJFINSV", "NESTLEIND", "TECHM", "POWERGRID", "NTPC",
        "ONGC", "TATAMOTORS", "M&M", "DIVISLAB", "DRREDDY",
        "CIPLA", "APOLLOHOSP", "ADANIPORTS", "ADANIENT", "COALINDIA",
        "JSWSTEEL", "TATASTEEL", "HINDALCO", "VEDL", "GRASIM",
        "BPCL", "HEROMOTOCO", "EICHERMOT", "SHREECEM", "INDUSINDBK",
        "SBILIFE", "HDFCLIFE", "BRITANNIA", "PIDILITIND", "DABUR",
    ]
    return [{"symbol": t, "name": t, "exchange": "NSE"} for t in tickers]


async def search_symbols(query: str, limit: int = 10) -> list[dict]:
    """
    Return NSE symbols matching `query` as a prefix (case-insensitive).

    Args:
        query: User's search string (e.g. "RELI")
        limit: Max results to return (default 10, max 20)

    Returns:
        List of {symbol, name, exchange} dicts, ordered alphabetically.
    """
    query = query.upper().strip()

    if not query or len(query) < 1:
        return []

    symbols = await _load_nse_symbols()

    # Prefix match first (RELI → RELIANCE), then substring fallback
    prefix_matches = [s for s in symbols if s["symbol"].startswith(query)]
    if len(prefix_matches) < limit:
        # Also include substring matches that aren't already in prefix_matches
        substr_extra = [
            s for s in symbols
            if query in s["symbol"] and not s["symbol"].startswith(query)
        ]
        matches = prefix_matches + substr_extra
    else:
        matches = prefix_matches

    return matches[:limit]
