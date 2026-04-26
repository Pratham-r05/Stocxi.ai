"""
base.py — Core abstractions for the waterfall fetcher layer.

Every data fetch in Stocxi goes through this layer:
  1. A client (nse_client, bse_client, etc.) wraps a data source and exposes
     async methods that return raw dict payloads (or raise on failure).
  2. The caller builds a list of (source_id, confidence, async_fn) tuples in
     priority order — the waterfall chain.
  3. WaterfallRunner iterates the list, calls each fn, and returns the first
     successful FetchResult. All failures are logged.

FetchResult is the single return type crossing all fetcher boundaries.
Never return raw dicts from a fetcher — always wrap in FetchResult.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from backend.util.ist_calendar import now_ist

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class FetchResult:
    """
    Returned by every fetcher call.

    Args:
        ok: True if fetch succeeded and payload is populated.
        source_id: ID from config/sources.yaml (e.g. "nse_library").
        confidence: Source confidence score (0–1) from sources.yaml.
        payload: Raw data dict on success; None on failure.
        error: Human-readable error string on failure; None on success.
        fetched_at_ist: IST timestamp of the fetch attempt.
        request_id: End-to-end trace ID (empty string if not provided).
    """
    ok: bool
    source_id: str
    confidence: float
    payload: dict[str, Any] | None
    error: str | None
    fetched_at_ist: datetime
    request_id: str = ""

    @classmethod
    def success(
        cls,
        source_id: str,
        confidence: float,
        payload: dict[str, Any],
        request_id: str = "",
    ) -> "FetchResult":
        """Convenience constructor for a successful fetch."""
        return cls(
            ok=True,
            source_id=source_id,
            confidence=confidence,
            payload=payload,
            error=None,
            fetched_at_ist=now_ist(),
            request_id=request_id,
        )

    @classmethod
    def failure(
        cls,
        source_id: str,
        confidence: float,
        error: str,
        request_id: str = "",
    ) -> "FetchResult":
        """Convenience constructor for a failed fetch."""
        return cls(
            ok=False,
            source_id=source_id,
            confidence=confidence,
            payload=None,
            error=error,
            fetched_at_ist=now_ist(),
            request_id=request_id,
        )


# ── All-levels-failed sentinel ────────────────────────────────────────────────

@dataclass
class WaterfallFailure(Exception):
    """
    Raised by WaterfallRunner when all levels are exhausted without a success.

    Attributes:
        errors: Ordered list of (source_id, error_message) for each failed level.
    """
    errors: list[tuple[str, str]] = field(default_factory=list)

    def __str__(self) -> str:
        parts = [f"{sid}: {err}" for sid, err in self.errors]
        return "All waterfall levels failed — " + "; ".join(parts)


# ── Waterfall runner ──────────────────────────────────────────────────────────

Level = tuple[str, float, Callable[[], Awaitable[dict[str, Any]]]]
"""
A single waterfall level: (source_id, confidence, async_fetch_fn).

  source_id   — ID string matching config/sources.yaml.
  confidence  — Source confidence score from sources.yaml (0–1).
  async_fn    — Async callable taking no args, returning a raw dict payload.
                Raises any exception on failure.
"""


class WaterfallRunner:
    """
    Iterates a priority-ordered list of fetch levels, returning the first
    successful FetchResult. All failures are logged with their source_id.

    Usage:
        runner = WaterfallRunner()
        result = await runner.run([
            ("nse_library", 1.0, lambda: nse_client.fetch_quote(symbol)),
            ("bse_library", 1.0, lambda: bse_client.fetch_quote(bse_code)),
            ("yfinance",    0.7, lambda: yf_client.fetch_quote(symbol)),
        ], request_id=req.request_id)

    Raises:
        WaterfallFailure: if every level fails.
    """

    async def run(
        self,
        levels: list[Level],
        request_id: str = "",
    ) -> FetchResult:
        """
        Try each level in order; return the first OK result.

        Args:
            levels: Priority-ordered list of (source_id, confidence, async_fn).
            request_id: Trace ID forwarded into the FetchResult.

        Returns:
            FetchResult with ok=True from the first succeeding level.

        Raises:
            WaterfallFailure: all levels exhausted without success.
        """
        errors: list[tuple[str, str]] = []

        for source_id, confidence, fetch_fn in levels:
            try:
                payload = await fetch_fn()
                if not isinstance(payload, dict):
                    raise TypeError(f"fetch_fn returned {type(payload).__name__}, expected dict")
                result = FetchResult.success(source_id, confidence, payload, request_id)
                logger.debug("Waterfall OK: source=%s request_id=%s", source_id, request_id)
                return result

            except asyncio.CancelledError:
                raise  # never swallow task cancellation

            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Waterfall level failed: source=%s request_id=%s error=%s",
                    source_id, request_id, msg,
                )
                errors.append((source_id, msg))

        raise WaterfallFailure(errors=errors)


# ── Module-level singleton ────────────────────────────────────────────────────

waterfall = WaterfallRunner()
"""Module-level WaterfallRunner singleton. Import and use directly."""
