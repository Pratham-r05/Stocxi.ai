"""
routers/search.py — Autocomplete endpoint for NSE stock symbols.

Endpoint:
  GET /api/v1/search?q={query}&limit={n}

Behaviour:
  - Prefix match first (RELI → RELIANCE), then substring fallback
  - Returns up to `limit` results (default 10, max 20)
  - Cached in Redis for 1 hour per query string
  - Returns empty list (not 404) for no matches — frontend handles empty state

Caching:
  TTL_SEARCH = 3600s  (from redis_client.py)
"""

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from cache.redis_client import cache_get, cache_set, TTL_SEARCH
from services.search_service import search_symbols

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search", tags=["Search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1, max_length=20, description="Symbol prefix to search"),
    limit: int = Query(default=10, ge=1, le=20, description="Max results (1-20)"),
):
    """
    Autocomplete NSE stock symbols by prefix.

    Examples:
      /api/v1/search?q=RELI         → [{symbol: "RELIANCE", ...}, ...]
      /api/v1/search?q=TCS          → [{symbol: "TCS", ...}]
      /api/v1/search?q=HDFC&limit=5 → top 5 HDFC-prefixed symbols
    """
    query = q.upper().strip()
    cache_key = f"search:{query}:{limit}"

    # ── Cache hit ──────────────────────────────────────────────────────────────
    cached = await cache_get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return JSONResponse(content=cached)

    # ── Search ─────────────────────────────────────────────────────────────────
    results = await search_symbols(query, limit=limit)

    response = {
        "query":   query,
        "count":   len(results),
        "results": results,
    }

    # Only cache non-empty results (empty may just mean NSE hasn't loaded)
    if results:
        await cache_set(cache_key, response, TTL_SEARCH)

    return JSONResponse(content=response)
