"""
store.py — Postgres persistence for knowledge graph nodes and edges.

Writes to the tables defined in backend/db/migrations/001_initial_schema.sql:
  nodes      (partitioned by as_of_date monthly)
  node_edges (from_id, to_id, relation, strength, analysis_id)

All writes are upsert-safe (ON CONFLICT DO UPDATE). Reads support recursive CTE
traversal for subgraph extraction by analysis_id.

Connection: reads DATABASE_URL from environment (set in .env).
            Uses asyncpg for async Postgres access.

This module is lazy-import safe: if asyncpg is not installed (dev/test without DB),
imports succeed but calls raise RuntimeError with a clear message.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

from backend.graph.builder import Edge
from backend.schemas.node import Node

logger = logging.getLogger(__name__)

# ── asyncpg lazy import ───────────────────────────────────────────────────────

try:
    import asyncpg  # type: ignore
    _HAS_ASYNCPG = True
except ImportError:
    asyncpg = None  # type: ignore
    _HAS_ASYNCPG = False


def _require_asyncpg() -> None:
    """Raise a clear error if asyncpg is not installed."""
    if not _HAS_ASYNCPG:
        raise RuntimeError(
            "asyncpg is not installed. Run: pip install asyncpg>=0.29 "
            "or add it to backend/requirements.txt"
        )


async def _get_conn() -> Any:
    """Open a single asyncpg connection from DATABASE_URL env var."""
    _require_asyncpg()
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Add it to .env")
    return await asyncpg.connect(url)


# ── Write nodes ───────────────────────────────────────────────────────────────

async def write_nodes(
    nodes: list[Node],
    analysis_id: str,
) -> int:
    """
    Upsert a batch of nodes into the `nodes` table.

    Args:
        nodes:       Nodes to persist.
        analysis_id: Trace ID for this analysis run.

    Returns:
        Number of rows written.

    Raises:
        RuntimeError: if asyncpg missing or DATABASE_URL unset.
        asyncpg.PostgresError: on DB write failure.
    """
    if not nodes:
        return 0

    conn = await _get_conn()
    try:
        rows = [_node_to_row(n, analysis_id) for n in nodes]
        await conn.executemany(
            """
            INSERT INTO nodes (
                node_id, analysis_id, stock, category, name,
                value, value_raw, signal, confidence, source, source_url,
                as_of_date, fetched_at_ist, horizon_relevance,
                weight, weight_version, schema_version, sanitized
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18
            )
            ON CONFLICT (node_id) DO UPDATE SET
                analysis_id      = EXCLUDED.analysis_id,
                value            = EXCLUDED.value,
                value_raw        = EXCLUDED.value_raw,
                signal           = EXCLUDED.signal,
                confidence       = EXCLUDED.confidence,
                fetched_at_ist   = EXCLUDED.fetched_at_ist,
                weight           = EXCLUDED.weight,
                sanitized        = EXCLUDED.sanitized
            """,
            rows,
        )
        logger.info("store.write_nodes: wrote %d nodes (analysis_id=%s)", len(rows), analysis_id)
        return len(rows)
    finally:
        await conn.close()


def _node_to_row(node: Node, analysis_id: str) -> tuple:
    """Convert a Node pydantic model to a flat tuple for asyncpg executemany."""
    return (
        node.node_id,
        analysis_id,
        node.stock,
        node.category.value,
        node.name,
        node.value,
        json.dumps(node.value_raw, ensure_ascii=False, default=str),
        node.signal.value,
        node.confidence,
        node.source,
        node.source_url,
        node.as_of_date,
        node.fetched_at_ist,
        node.horizon_relevance.value,
        node.weight,
        node.weight_version,
        node.schema_version,
        node.sanitized,
    )


# ── Write edges ───────────────────────────────────────────────────────────────

async def write_edges(
    edges: list[Edge],
    analysis_id: str,
) -> int:
    """
    Upsert a batch of edges into the `node_edges` table.

    Args:
        edges:       Edges from builder.build_edges().
        analysis_id: Trace ID for this analysis run.

    Returns:
        Number of rows written.

    Raises:
        RuntimeError: if asyncpg missing or DATABASE_URL unset.
        asyncpg.PostgresError: on DB write failure.
    """
    if not edges:
        return 0

    conn = await _get_conn()
    try:
        rows = [
            (e.from_id, e.to_id, e.relation, e.strength, analysis_id)
            for e in edges
        ]
        await conn.executemany(
            """
            INSERT INTO node_edges (from_id, to_id, relation, strength, analysis_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (from_id, to_id, relation, analysis_id) DO UPDATE SET
                strength = EXCLUDED.strength
            """,
            rows,
        )
        logger.info("store.write_edges: wrote %d edges (analysis_id=%s)", len(rows), analysis_id)
        return len(rows)
    finally:
        await conn.close()


# ── Read ──────────────────────────────────────────────────────────────────────

async def read_nodes_by_analysis(analysis_id: str) -> list[dict]:
    """
    Fetch all nodes for an analysis run.

    Args:
        analysis_id: Trace ID from a previous write_nodes() call.

    Returns:
        List of raw row dicts (not pydantic models — use for audit/admin only).

    Raises:
        RuntimeError: if asyncpg missing or DATABASE_URL unset.
    """
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            "SELECT * FROM nodes WHERE analysis_id = $1 ORDER BY category, name",
            analysis_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def read_subgraph(
    analysis_id: str,
    root_node_id: str,
    max_depth: int = 3,
) -> dict[str, Any]:
    """
    Retrieve a subgraph rooted at root_node_id via recursive CTE traversal.

    Args:
        analysis_id:  Trace ID.
        root_node_id: Starting node for BFS traversal.
        max_depth:    Maximum edge hops to follow.

    Returns:
        Dict with {"nodes": [...], "edges": [...]} — raw dicts for admin view.

    Raises:
        RuntimeError: if asyncpg missing or DATABASE_URL unset.
    """
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            """
            WITH RECURSIVE subgraph AS (
                SELECT from_id, to_id, relation, strength, 0 AS depth
                FROM node_edges
                WHERE from_id = $1 AND analysis_id = $2

                UNION ALL

                SELECT e.from_id, e.to_id, e.relation, e.strength, sg.depth + 1
                FROM node_edges e
                JOIN subgraph sg ON e.from_id = sg.to_id
                WHERE sg.depth < $3 AND e.analysis_id = $2
            )
            SELECT DISTINCT * FROM subgraph
            """,
            root_node_id, analysis_id, max_depth,
        )
        edges_raw = [dict(r) for r in rows]

        # Collect all involved node IDs
        all_ids: set[str] = {root_node_id}
        for e in edges_raw:
            all_ids.add(e["from_id"]); all_ids.add(e["to_id"])

        node_rows = await conn.fetch(
            "SELECT * FROM nodes WHERE node_id = ANY($1::text[])",
            list(all_ids),
        )
        return {
            "nodes": [dict(r) for r in node_rows],
            "edges": edges_raw,
        }
    finally:
        await conn.close()
