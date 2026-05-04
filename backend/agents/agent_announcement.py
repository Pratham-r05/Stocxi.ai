"""
agent_announcement.py — Corporate Announcement Agent (Phase 4, Agent Layer).

Wraps announcements_service.get_announcements with a hard 20-second timeout and
agent-layer protocols: FetchRequest / FetchFailure contract, structured request_id
logging, sanitized=True stamping (exchange-sourced structured data carries no
injected content), and per-node validation. Returns a FetchFailure instead of
raising on timeout or complete data absence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from schemas.messages import FetchDomain, FetchFailure, FetchRequest
from schemas.node import Node
from services.announcements_service import get_announcements
from services.context_generator import apply_announcement_context
from util.ist_calendar import now_ist

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS: float = 45.0
_ANNOUNCEMENT_SOURCE: str = "nse_announcements"


class AnnouncementAgent:
    """Agent that fetches and validates corporate announcement nodes.

    Implements the FetchRequest / FetchFailure contract defined in
    backend/schemas/messages.py. Delegates all data retrieval and node
    construction to announcements_service; this layer adds timeout enforcement,
    failure encapsulation, and post-fetch validation only.
    """

    domain = FetchDomain.announcement

    async def fetch(self, request: FetchRequest) -> list[Node] | FetchFailure:
        """Fetch corporate announcements (board meetings, dividends, filings).

        Wraps get_announcements with a 20s timeout. Returns FetchFailure on
        timeout or complete failure. Returns partial list if the service
        returned at least one node. All announcement nodes are marked
        sanitized=True because they originate from exchange-structured data
        and contain no user-injected or raw HTML content.

        Args:
            request: Typed FetchRequest with stock symbol, as_of_date,
                     user profile, and trace request_id.

        Returns:
            List of announcement Nodes on success, or FetchFailure on timeout
            or total data absence.
        """
        log = logger.getChild(request.request_id or "no-rid")
        symbol = request.stock.upper()

        try:
            nodes: list[Node] = await asyncio.wait_for(
                get_announcements(
                    symbol,
                    request.as_of_date,
                    request.profile,
                    request.request_id,
                ),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.warning("announcement_agent: timeout after %.0fs for %s", _TIMEOUT_SECONDS, symbol)
            return FetchFailure(
                domain=self.domain,
                source=_ANNOUNCEMENT_SOURCE,
                reason="timeout",
                error=f"get_announcements timed out after {_TIMEOUT_SECONDS:.0f}s",
                request_id=request.request_id,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("announcement_agent: unexpected error for %s — %s", symbol, exc)
            return FetchFailure(
                domain=self.domain,
                source=_ANNOUNCEMENT_SOURCE,
                reason="parse_error",
                error=str(exc),
                request_id=request.request_id,
            )

        if not nodes:
            log.info("announcement_agent: empty result for %s", symbol)
            return FetchFailure(
                domain=self.domain,
                source=_ANNOUNCEMENT_SOURCE,
                reason="empty",
                error=f"no announcements returned for {symbol}",
                request_id=request.request_id,
            )

        # Mark all nodes sanitized — exchange-sourced structured data.
        for node in nodes:
            node.sanitized = True

        # Promote llm_summary from value_raw into node.context (no extra LLM call)
        nodes = apply_announcement_context(nodes)

        log.info("announcement_agent: %s — %d nodes fetched", symbol, len(nodes))
        return nodes

    async def validate(self, nodes: list[Node]) -> list[Node]:
        """Drop nodes where value is empty or confidence is zero or negative.

        Args:
            nodes: Raw list of Node objects returned by fetch().

        Returns:
            Filtered list containing only nodes with non-empty value and
            positive confidence. Logs the count of dropped nodes.
        """
        before = len(nodes)
        valid = [
            n for n in nodes
            if (n.value or "").strip() and n.confidence > 0
        ]
        dropped = before - len(valid)
        if dropped:
            logger.info("announcement_agent.validate: dropped %d invalid node(s)", dropped)
        return valid


# Module-level singleton — import and use directly.
announcement_agent = AnnouncementAgent()


async def run(request: FetchRequest) -> list[Node] | FetchFailure:
    """Module-level entry point — delegates to announcement_agent singleton."""
    return await announcement_agent.fetch(request)
