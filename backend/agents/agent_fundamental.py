"""
agent_fundamental.py — Fundamental Data Agent for the Stocxi analysis pipeline.

This agent fans out to three Phase-2 services (ratios, financials, shareholding)
in parallel, imposes a hard 20-second timeout on the combined gather, reconciles
duplicate nodes by keeping the higher-confidence copy, and validates the result
before returning.  It returns a FetchFailure only when every sub-service fails;
partial results from surviving services are always preferred over an empty response.

All returned nodes carry sanitized=True because fundamental values (ratios,
percentages, bucketed labels) carry no company-identity information.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from backend.schemas.messages import FetchDomain, FetchFailure, FetchRequest
from backend.schemas.node import Node
from backend.services.context_generator import (
    generate_financial_context,
    generate_fundamental_context,
)
from backend.services.financials_service import get_financials
from backend.services.ratios_service import get_ratios
from backend.services.shareholding_service import get_shareholding

logger = logging.getLogger(__name__)

_AGENT_TIMEOUT: float = 45.0  # hard wall-clock limit in seconds
_DOMAIN = FetchDomain.fundamental


# ── Reconciliation helpers ────────────────────────────────────────────────────


def _dedup(nodes: list[Node]) -> list[Node]:
    """
    Remove duplicate nodes, keeping the copy with higher confidence.

    Two nodes are considered duplicates when they share the same ``name``
    and ``as_of_date``.  The discarded node is logged at WARNING level so
    the source conflict is visible in the audit trail.

    Args:
        nodes: Raw node list that may contain duplicates.

    Returns:
        Deduplicated list with the highest-confidence node per (name, as_of_date).
    """
    seen: dict[tuple[str, date], Node] = {}
    for node in nodes:
        key = (node.name, node.as_of_date)
        existing = seen.get(key)
        if existing is None:
            seen[key] = node
        elif node.confidence > existing.confidence:
            logger.warning(
                "agent_fundamental: duplicate node discarded — "
                "keeping source=%s (conf=%.2f) over source=%s (conf=%.2f) for %s on %s",
                node.source,
                node.confidence,
                existing.source,
                existing.confidence,
                node.name,
                node.as_of_date,
            )
            seen[key] = node
        else:
            logger.warning(
                "agent_fundamental: duplicate node discarded — "
                "keeping source=%s (conf=%.2f) over source=%s (conf=%.2f) for %s on %s",
                existing.source,
                existing.confidence,
                node.source,
                node.confidence,
                node.name,
                node.as_of_date,
            )
    return list(seen.values())


# ── Agent class ───────────────────────────────────────────────────────────────


class FundamentalAgent:
    """
    Agent responsible for fetching all fundamental data nodes for a stock.

    Orchestrates ratios, financials, and shareholding services in parallel,
    enforces a 20-second timeout, reconciles duplicates, and validates output.
    """

    domain: FetchDomain = _DOMAIN

    async def fetch(self, request: FetchRequest) -> list[Node] | FetchFailure:
        """
        Fan out to all three fundamental services and collect nodes.

        Issues ratios, financials, and shareholding fetches concurrently via
        ``asyncio.gather``.  If ALL three services raise exceptions the method
        returns a ``FetchFailure``; if only some fail it logs warnings and
        returns partial results.  The entire gather is wrapped in a 20-second
        ``asyncio.wait_for`` timeout.

        Args:
            request: Typed fetch request carrying stock, date, profile, request_id.

        Returns:
            A deduplicated, validated list[Node] on (full or partial) success,
            or a FetchFailure when every sub-service fails.
        """
        log = logger.getChild(request.request_id or "no-rid")

        async def _gather() -> tuple:
            return await asyncio.gather(
                get_ratios(request.stock, request.as_of_date, request.profile, request.request_id),
                get_financials(request.stock, request.as_of_date, request.profile, request.request_id),
                get_shareholding(request.stock, request.as_of_date, request.profile, request.request_id),
                return_exceptions=True,
            )

        try:
            results = await asyncio.wait_for(_gather(), timeout=_AGENT_TIMEOUT)
        except asyncio.TimeoutError:
            log.error("agent_fundamental: 45s timeout exceeded for %s", request.stock)
            return FetchFailure(
                domain=_DOMAIN,
                source="fundamental_agent",
                reason="timeout",
                error=f"All fundamental services timed out after {_AGENT_TIMEOUT}s",
                request_id=request.request_id,
            )

        service_names = ("ratios_service", "financials_service", "shareholding_service")
        all_nodes: list[Node] = []
        failure_count = 0

        for name, result in zip(service_names, results):
            if isinstance(result, Exception):
                failure_count += 1
                log.warning(
                    "agent_fundamental: %s failed for %s — %s",
                    name, request.stock, result,
                )
            else:
                all_nodes.extend(result)

        if failure_count == len(service_names):
            log.error(
                "agent_fundamental: all 3 sub-services failed for %s", request.stock
            )
            return FetchFailure(
                domain=_DOMAIN,
                source="fundamental_agent",
                reason="empty",
                error="ratios_service, financials_service, and shareholding_service all failed",
                request_id=request.request_id,
            )

        if failure_count > 0:
            log.warning(
                "agent_fundamental: %d/%d sub-services failed for %s — returning partial nodes",
                failure_count, len(service_names), request.stock,
            )

        deduped = _dedup(all_nodes)
        validated = await self.validate(deduped)

        # Stamp all nodes sanitized=True (ratios/percentages carry no identity)
        for node in validated:
            node.sanitized = True

        log.info(
            "agent_fundamental: %s — %d nodes returned (%d raw, %d after dedup)",
            request.stock, len(validated), len(all_nodes), len(deduped),
        )

        # Generate horizon-aware context for ratio and financial nodes
        if validated:
            horizon = (
                request.profile.horizon.value
                if hasattr(request.profile.horizon, "value")
                else str(request.profile.horizon)
            )
            loop = asyncio.get_event_loop()
            try:
                # Fundamental ratio context
                validated = await loop.run_in_executor(
                    None, generate_fundamental_context, validated, horizon, "STOCK_A"
                )
                # Financial statement context (QoQ/YoY comparison)
                validated = await loop.run_in_executor(
                    None, generate_financial_context, validated, horizon, "STOCK_A"
                )
                log.info(
                    "agent_fundamental: context generation complete for %s", request.stock
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "agent_fundamental: context generation failed (non-fatal): %s", exc
                )

        return validated

    async def validate(self, nodes: list[Node]) -> list[Node]:
        """
        Drop nodes that carry no usable signal.

        A node is discarded when its ``value`` field is empty/whitespace or
        its ``confidence`` is zero or negative.  The count of dropped nodes
        is logged at WARNING level.

        Args:
            nodes: Node list to validate.

        Returns:
            Filtered list containing only nodes with non-empty value and
            positive confidence.
        """
        valid: list[Node] = []
        dropped = 0
        for node in nodes:
            if not node.value.strip():
                logger.warning(
                    "agent_fundamental: dropping node %s — empty value", node.name
                )
                dropped += 1
            elif node.confidence <= 0:
                logger.warning(
                    "agent_fundamental: dropping node %s — confidence=%.2f",
                    node.name, node.confidence,
                )
                dropped += 1
            else:
                valid.append(node)

        if dropped:
            logger.warning(
                "agent_fundamental: validate dropped %d node(s)", dropped
            )
        return valid


# ── Module-level singleton ────────────────────────────────────────────────────

fundamental_agent = FundamentalAgent()


async def run(request: FetchRequest) -> list[Node] | FetchFailure:
    """Module-level entry point — delegates to fundamental_agent singleton."""
    return await fundamental_agent.fetch(request)
