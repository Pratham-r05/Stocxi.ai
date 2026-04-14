"""
redis_client.py — Async Redis wrapper for Stocxi.

Why async redis?
  FastAPI is async-native; using the async redis client avoids blocking the
  event loop during cache reads/writes (which happen on every request).

Connection:
  Uses Upstash's rediss:// (TLS) URL from .env.
  redis-py auto-creates a connection pool — we use a single module-level
  client instead of opening/closing connections per request.

Public API (used by all services):
  await cache_get(key)          → dict | list | None
  await cache_set(key, val, ttl) → None
  await cache_delete(key)       → None
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

# ── Single shared client across the entire app ─────────────────────────────────
# decode_responses=True → redis-py returns str instead of bytes automatically
redis_client: aioredis.Redis = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,   # fail fast if Upstash unreachable
    socket_timeout=5,
)


async def cache_get(key: str) -> Any | None:
    """
    Fetch a cached value by key.
    Returns deserialized Python object or None on miss / error.
    Never raises — a cache miss is not an error; callers fall through to live fetch.
    """
    try:
        raw = await redis_client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        # Log but never crash — degrade gracefully to live data
        logger.warning(f"Redis GET failed for key '{key}': {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """
    Store a value in Redis with a TTL (seconds).
    Serializes to JSON so any dict/list can be stored.
    Never raises — failing to cache is non-fatal.
    """
    try:
        serialized = json.dumps(value, default=str)  # default=str handles datetime etc.
        await redis_client.setex(key, ttl, serialized)
    except Exception as e:
        logger.warning(f"Redis SET failed for key '{key}': {e}")


async def cache_delete(key: str) -> None:
    """
    Invalidate a specific cache key.
    Used when forcing a fresh fetch (e.g. user explicitly refreshes).
    """
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.warning(f"Redis DELETE failed for key '{key}': {e}")


# ── TTL constants (from AI_CONTEXT.md) ────────────────────────────────────────
# Centralised here so they never drift between services
TTL_OVERVIEW = 300          # stock:overview:{symbol}       → 5 min
TTL_FINANCIALS = 604_800    # stock:financials:{symbol}     → 7 days (quarterly data)
TTL_NEWS = 7_200            # stock:news:{symbol}           → 2 hrs
TTL_ANALYSIS = 21_600       # stock:analysis:{symbol}:{risk}→ 6 hrs
TTL_SEARCH = 3_600          # search:{query}                → 1 hr
