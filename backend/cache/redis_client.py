"""
redis_client.py — Async Redis wrapper for Stocxi.

Connection is lazy-initialised on first use so importing this module
never fails at test/CLI time when REDIS_URL is not set.

Public API:
  await cache_get(key)           → dict | list | None
  await cache_set(key, val, ttl) → None
  await cache_delete(key)        → None
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        from config import settings
        _client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client


async def cache_get(key: str) -> Any | None:
    """Return deserialized object or None on miss / error. Never raises."""
    try:
        raw = await _get_client().get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("Redis GET failed for key '%s': %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """Store value as JSON with TTL (seconds). Never raises."""
    try:
        serialized = json.dumps(value, default=str)
        await _get_client().setex(key, ttl, serialized)
    except Exception as e:
        logger.warning("Redis SET failed for key '%s': %s", key, e)


async def cache_delete(key: str) -> None:
    """Invalidate a cache key. Never raises."""
    try:
        await _get_client().delete(key)
    except Exception as e:
        logger.warning("Redis DELETE failed for key '%s': %s", key, e)


async def ping() -> bool:
    """Ping Redis. Returns True on success, False on failure. Never raises."""
    try:
        await _get_client().ping()
        return True
    except Exception:
        return False


# ── TTL constants ──────────────────────────────────────────────────────────────
TTL_OVERVIEW        = 300        # stock:overview:{symbol}            → 5 min
TTL_FINANCIALS      = 604_800    # stock:financials:{symbol}          → 7 days
TTL_NEWS            = 7_200      # stock:news:{symbol}                → 2 hrs
TTL_SEARCH          = 3_600      # search:{query}                     → 1 hr
TTL_ANALYSIS_RESULT = 7_200      # analysis:v{pv}:{wv}:{s}:{pb}:{dh} → 2 hrs
                                 # (data_hash in key ensures correctness; 2h avoids
                                 #  stale intraday announcements sitting 24h)
