"""
agent_technical.py — Technical Data Agent for the Stocxi Agent Layer (Phase 4).

This module wraps the Phase 2 `get_technicals` service with the agent protocol
defined in AGENTS.md: typed FetchRequest / FetchFailure messages, a hard 20-second
timeout, structured logging keyed by request_id, post-fetch validation, and a
module-level singleton that the orchestrator calls directly. All nodes are marked
sanitized=True because technical numbers carry no stock identity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from backend.schemas.messages import FetchDomain, FetchFailure, FetchRequest
from backend.schemas.node import Node
from backend.services.technicals_service import get_technicals

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT_SECONDS: int = 20


class TechnicalAgent:
    """
    Agent that fetches and validates technical indicator nodes for a given stock.

    Wraps `get_technicals` with the standard agent protocol:
    - Hard timeout via asyncio.wait_for
    - Returns FetchFailure (never raises) on any error
    - Validates nodes before returning them to the orchestrator
    - Marks all nodes sanitized=True
    """

    domain: FetchDomain = FetchDomain.technical

    async def fetch(self, request: FetchRequest) -> list[Node] | FetchFailure:
        """
        Fetch technical indicator nodes for the requested stock.

        Delegates to `get_technicals`, enforces a 20-second timeout, marks all
        returned nodes as sanitized, then passes them through validate().

        Args:
            request: A FetchRequest containing stock symbol, as_of_date, profile,
                     and request_id.

        Returns:
            A validated list[Node] on success, or a FetchFailure on any error
            (timeout, parse error, empty result, etc.). Never raises.
        """
        rid = request.request_id
        symbol = request.stock.upper()
        logger.info("[%s] TechnicalAgent.fetch — start for %s", rid, symbol)

        try:
            nodes: list[Node] = await asyncio.wait_for(
                get_technicals(
                    symbol=symbol,
                    as_of_date=request.as_of_date,
                    profile=request.profile,
                    request_id=rid,
                ),
                timeout=_FETCH_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[%s] TechnicalAgent.fetch — timeout after %ds for %s",
                rid, _FETCH_TIMEOUT_SECONDS, symbol,
            )
            return self._failure(rid, "timeout", f"Timed out after {_FETCH_TIMEOUT_SECONDS}s")
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[%s] TechnicalAgent.fetch — unexpected error for %s: %s",
                rid, symbol, exc,
            )
            return self._failure(rid, "parse_error", str(exc))

        for node in nodes:
            node.sanitized = True

        validated = await self.validate(nodes)
        logger.info(
            "[%s] TechnicalAgent.fetch — %d nodes returned (%d after validation)",
            rid, len(nodes), len(validated),
        )
        return validated

    async def validate(self, nodes: list[Node]) -> list[Node]:
        """
        Drop nodes that carry no usable signal.

        A node is dropped if its `value` field is empty (blank string) or its
        `confidence` is <= 0. Logs the count of dropped nodes.

        Args:
            nodes: Raw list of Node objects returned by the service.

        Returns:
            Filtered list containing only nodes with a non-empty value and
            positive confidence.
        """
        valid = [n for n in nodes if n.value.strip() and n.confidence > 0]
        dropped = len(nodes) - len(valid)
        if dropped:
            logger.warning(
                "TechnicalAgent.validate — dropped %d invalid node(s) out of %d",
                dropped, len(nodes),
            )
        return valid

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _failure(
        self,
        request_id: str,
        reason: Literal["timeout", "blocked", "parse_error", "unapproved_source", "empty", "rate_limited"],
        error: str,
    ) -> FetchFailure:
        """Build a FetchFailure for this domain."""
        return FetchFailure(
            domain=self.domain,
            source="technicals_service",
            reason=reason,
            error=error,
            request_id=request_id,
        )


# Module-level singleton — orchestrator imports and calls this directly.
technical_agent = TechnicalAgent()


async def run(request: FetchRequest) -> list[Node] | FetchFailure:
    """Module-level entry point — delegates to technical_agent singleton."""
    return await technical_agent.fetch(request)
